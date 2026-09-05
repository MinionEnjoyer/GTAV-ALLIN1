#include "allin1/map_host.hpp"

#include <cstdlib>
#include <iostream>
#include <set>
#include <string>
#include <vector>

using namespace allin1::maps;

namespace {

int failures = 0;

#define CHECK(condition)                                                       \
    do {                                                                       \
        if (!(condition)) {                                                    \
            std::cerr << __FILE__ << ':' << __LINE__                           \
                      << " CHECK failed: " #condition << '\n';                \
            ++failures;                                                        \
        }                                                                      \
    } while (false)

class FakeLogger final : public ILogger {
public:
    std::vector<LogEvent> events;
    void Write(const LogEvent& event) noexcept override {
        events.push_back(event);
    }
};

class FakeBackend final : public IMapGroupBackend {
public:
    int acquire_count = 0;
    int release_count = 0;
    bool acquire_succeeds = true;
    bool release_succeeds = true;
    std::vector<std::string> acquired;
    std::vector<std::string> released;

    bool Acquire(const AllowedGroup& group,
                 std::string& error) noexcept override {
        ++acquire_count;
        acquired.emplace_back(group.group_name);
        if (!acquire_succeeds) error = "fixture acquire failure";
        return acquire_succeeds;
    }
    bool Release(const AllowedGroup& group,
                 std::string& error) noexcept override {
        ++release_count;
        released.emplace_back(group.group_name);
        if (!release_succeeds) error = "fixture release failure";
        return release_succeeds;
    }
};

PackReceipt Receipt(Edition edition) {
    PackReceipt receipt;
    receipt.schema = 1;
    receipt.status = "verified";
    receipt.package_id = kExpectedPackageId;
    receipt.pack_name = kExpectedPackName;
    receipt.layout = kExpectedLayout;
    receipt.edition = edition;
    receipt.archive_bytes = 123456;
    receipt.archive_sha256 = std::string(64, 'a');
    for (const AllowedGroup& group : Allowlist())
        receipt.groups.push_back({group.property, group.property_key,
                                  group.group_name, group.changeset_name});
    return receipt;
}

PackEvidence Evidence() {
    PackEvidence evidence;
    evidence.marker_layout = kExpectedLayout;
    evidence.marker_archive_registration = kExpectedArchiveRegistration;
    evidence.marker_activation = kExpectedActivation;
    evidence.actual_archive_bytes = 123456;
    evidence.actual_archive_sha256 = std::string(64, 'A');
    return evidence;
}

void TestAllowlistIsFixedAndUnique() {
    CHECK(Allowlist().size() == 6);
    std::set<Property> properties;
    std::set<std::string> groups;
    for (const auto& item : Allowlist()) {
        CHECK(properties.insert(item.property).second);
        CHECK(groups.insert(item.group_name).second);
        CHECK(std::string(item.group_name).find("ALLIN1_MAP_") == 0);
    }
    CHECK(FindAllowedGroup(static_cast<Property>(255)) == nullptr);
}

void TestDefaultDisabledAndNoStartupActivation() {
    FakeBackend backend;
    FakeLogger logger;
    MapHost host(Edition::Enhanced, backend, logger);
    CHECK(backend.acquire_count == 0);
    CHECK(host.Prepare(Receipt(Edition::Enhanced), Evidence()).success);
    CHECK(backend.acquire_count == 0);
    const auto denied = host.Acquire(Property::Davis);
    CHECK(!denied.success);
    CHECK(denied.code == OperationCode::Disabled);
    CHECK(backend.acquire_count == 0);
    CHECK(host.SetEnabled(true).success);
    CHECK(backend.acquire_count == 0);
}

void TestReceiptFailsClosed() {
    auto receipt = Receipt(Edition::Legacy);
    auto evidence = Evidence();
    CHECK(ValidateReceipt(Edition::Legacy, receipt, evidence));

    receipt.groups[0].group_name = "GROUP_MAP";
    CHECK(ValidateReceipt(Edition::Legacy, receipt, evidence).code ==
          ValidationCode::GroupMismatch);
    receipt = Receipt(Edition::Legacy);
    receipt.groups.push_back(receipt.groups.front());
    CHECK(ValidateReceipt(Edition::Legacy, receipt, evidence).code ==
          ValidationCode::UnknownGroup);
    receipt = Receipt(Edition::Legacy);
    receipt.groups[1] = receipt.groups[0];
    CHECK(ValidateReceipt(Edition::Legacy, receipt, evidence).code ==
          ValidationCode::DuplicateGroup);
    receipt = Receipt(Edition::Legacy);
    receipt.package_id = "other.package";
    CHECK(ValidateReceipt(Edition::Legacy, receipt, evidence).code ==
          ValidationCode::WrongPackage);
    receipt = Receipt(Edition::Legacy);
    receipt.edition = Edition::Enhanced;
    CHECK(ValidateReceipt(Edition::Legacy, receipt, evidence).code ==
          ValidationCode::WrongEdition);
    receipt = Receipt(Edition::Legacy);
    evidence.marker_activation = "startup";
    CHECK(ValidateReceipt(Edition::Legacy, receipt, evidence).code ==
          ValidationCode::MarkerMismatch);
    evidence = Evidence();
    evidence.actual_archive_sha256 = std::string(64, 'b');
    CHECK(ValidateReceipt(Edition::Legacy, receipt, evidence).code ==
          ValidationCode::InvalidArchiveIdentity);
}

void TestReferenceCounting() {
    FakeBackend backend;
    FakeLogger logger;
    MapHost host(Edition::Legacy, backend, logger, HostOptions{true});
    CHECK(host.Prepare(Receipt(Edition::Legacy), Evidence()).success);
    CHECK(host.Acquire(Property::Harmony).code == OperationCode::Activated);
    CHECK(host.Acquire(Property::Harmony).code ==
          OperationCode::ReferenceAcquired);
    CHECK(backend.acquire_count == 1);
    auto snapshot = host.Snapshot();
    CHECK(snapshot.leases.size() == 1);
    CHECK(snapshot.leases[0].reference_count == 2);
    CHECK(host.Release(Property::Harmony).code ==
          OperationCode::ReferenceReleased);
    CHECK(backend.release_count == 0);
    CHECK(host.Release(Property::Harmony).code == OperationCode::Released);
    CHECK(backend.release_count == 1);
    CHECK(host.Snapshot().leases.empty());
}

void TestYachtResidentUntilShutdown() {
    FakeBackend backend;
    FakeLogger logger;
    MapHost host(Edition::Enhanced, backend, logger, HostOptions{true});
    CHECK(host.Prepare(Receipt(Edition::Enhanced), Evidence()).success);
    CHECK(host.Acquire(Property::Yacht).success);
    CHECK(host.Release(Property::Yacht).code == OperationCode::KeptResident);
    CHECK(backend.release_count == 0);
    CHECK(host.Snapshot().leases.size() == 1);
    CHECK(host.Shutdown());
    CHECK(backend.release_count == 1);
    CHECK(host.Snapshot().leases.empty());
}

void TestBackendFailureRetainsSafeState() {
    FakeBackend backend;
    FakeLogger logger;
    MapHost host(Edition::Legacy, backend, logger, HostOptions{true});
    CHECK(host.Prepare(Receipt(Edition::Legacy), Evidence()).success);
    backend.acquire_succeeds = false;
    CHECK(host.Acquire(Property::Paleto).code ==
          OperationCode::BackendFailure);
    CHECK(host.Snapshot().leases.empty());

    backend.acquire_succeeds = true;
    CHECK(host.Acquire(Property::Paleto).success);
    backend.release_succeeds = false;
    CHECK(host.Release(Property::Paleto).code ==
          OperationCode::BackendFailure);
    CHECK(host.Snapshot().leases.size() == 1);
    CHECK(!host.SetEnabled(false).success);
    backend.release_succeeds = true;
    CHECK(host.Shutdown());
    CHECK(host.SetEnabled(false).success);
}

void TestInvalidPropertyNeverCrossesBackend() {
    FakeBackend backend;
    FakeLogger logger;
    MapHost host(Edition::Enhanced, backend, logger, HostOptions{true});
    CHECK(host.Prepare(Receipt(Edition::Enhanced), Evidence()).success);
    CHECK(host.Acquire(static_cast<Property>(255)).code ==
          OperationCode::InvalidProperty);
    CHECK(backend.acquire_count == 0);
}

}  // namespace

int main() {
    TestAllowlistIsFixedAndUnique();
    TestDefaultDisabledAndNoStartupActivation();
    TestReceiptFailsClosed();
    TestReferenceCounting();
    TestYachtResidentUntilShutdown();
    TestBackendFailureRetainsSafeState();
    TestInvalidPropertyNeverCrossesBackend();
    if (failures != 0) {
        std::cerr << failures << " map-host policy test(s) failed\n";
        return EXIT_FAILURE;
    }
    std::cout << "map-host policy tests passed\n";
    return EXIT_SUCCESS;
}
