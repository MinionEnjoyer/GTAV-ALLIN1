#include "allin1/map_host.hpp"

#include <algorithm>
#include <cctype>
#include <set>
#include <utility>

namespace allin1::maps {
namespace {

constexpr std::array<AllowedGroup, 6> kAllowlist{{
#define ALLIN1_MAP_GROUP(symbol, key, group, changeset, resident) \
    {Property::symbol, key, group, changeset, resident},
#include "allin1/map_host_allowlist.inc"
#undef ALLIN1_MAP_GROUP
}};

bool Equals(const std::string& left, const char* right) {
    return left == right;
}

bool IsSha256(const std::string& value) {
    return value.size() == 64 && std::all_of(
        value.begin(), value.end(), [](unsigned char character) {
            return (character >= '0' && character <= '9') ||
                   (character >= 'a' && character <= 'f') ||
                   (character >= 'A' && character <= 'F');
        });
}

std::string Lower(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(),
                   [](unsigned char character) {
                       return static_cast<char>(std::tolower(character));
                   });
    return value;
}

ValidationResult Invalid(ValidationCode code, std::string detail) {
    return {code, std::move(detail)};
}

}  // namespace

const std::array<AllowedGroup, 6>& Allowlist() noexcept {
    return kAllowlist;
}

const AllowedGroup* FindAllowedGroup(Property property) noexcept {
    const auto found = std::find_if(
        kAllowlist.begin(), kAllowlist.end(), [property](const auto& group) {
            return group.property == property;
        });
    return found == kAllowlist.end() ? nullptr : &*found;
}

const char* EditionName(Edition edition) noexcept {
    switch (edition) {
    case Edition::Legacy:
        return "legacy";
    case Edition::Enhanced:
        return "enhanced";
    default:
        return "unknown";
    }
}

ValidationResult ValidateReceipt(Edition expected_edition,
                                 const PackReceipt& receipt,
                                 const PackEvidence& evidence) {
    if (receipt.schema != 1)
        return Invalid(ValidationCode::InvalidSchema,
                       "receipt schema must be 1");
    if (receipt.status != "verified")
        return Invalid(ValidationCode::InvalidStatus,
                       "receipt status must be verified");
    if (!Equals(receipt.package_id, kExpectedPackageId))
        return Invalid(ValidationCode::WrongPackage,
                       "receipt package_id is not ALLIN1 Online Content");
    if (!Equals(receipt.pack_name, kExpectedPackName))
        return Invalid(ValidationCode::WrongPack,
                       "receipt pack_name is not allin1_maps");
    if (!Equals(receipt.layout, kExpectedLayout))
        return Invalid(ValidationCode::WrongLayout,
                       "receipt layout is not the deferred property layout");
    if (receipt.edition != expected_edition)
        return Invalid(ValidationCode::WrongEdition,
                       "receipt edition does not match this host build");
    if (receipt.archive_bytes == 0 || evidence.actual_archive_bytes == 0 ||
        !IsSha256(receipt.archive_sha256) ||
        !IsSha256(evidence.actual_archive_sha256) ||
        receipt.archive_bytes != evidence.actual_archive_bytes ||
        Lower(receipt.archive_sha256) != Lower(evidence.actual_archive_sha256))
        return Invalid(ValidationCode::InvalidArchiveIdentity,
                       "receipt and observed archive identity disagree");
    if (!Equals(evidence.marker_layout, kExpectedLayout) ||
        !Equals(evidence.marker_archive_registration,
                kExpectedArchiveRegistration) ||
        !Equals(evidence.marker_activation, kExpectedActivation))
        return Invalid(ValidationCode::MarkerMismatch,
                       "installer marker does not authorize deferred hosting");
    if (receipt.groups.size() < kAllowlist.size())
        return Invalid(ValidationCode::MissingGroup,
                       "receipt omits one or more required property groups");
    if (receipt.groups.size() > kAllowlist.size())
        return Invalid(ValidationCode::UnknownGroup,
                       "receipt contains groups outside the fixed allowlist");

    std::set<Property> observed;
    for (const ReceiptGroup& item : receipt.groups) {
        const AllowedGroup* expected = FindAllowedGroup(item.property);
        if (expected == nullptr)
            return Invalid(ValidationCode::UnknownGroup,
                           "receipt contains an unknown property group");
        if (!observed.insert(item.property).second)
            return Invalid(ValidationCode::DuplicateGroup,
                           "receipt repeats a property group");
        if (item.property_key != expected->property_key ||
            item.group_name != expected->group_name ||
            item.changeset_name != expected->changeset_name)
            return Invalid(ValidationCode::GroupMismatch,
                           std::string("receipt identity mismatch for ") +
                               expected->property_key);
    }
    if (observed.size() != kAllowlist.size())
        return Invalid(ValidationCode::MissingGroup,
                       "receipt omits one or more required property groups");
    return {ValidationCode::Valid, "verified pack-scoped map receipt"};
}

MapHost::MapHost(Edition edition, IMapGroupBackend& backend, ILogger& logger,
                 HostOptions options)
    : edition_(edition), backend_(backend), logger_(logger),
      enabled_(options.enabled) {}

OperationResult MapHost::Prepare(const PackReceipt& receipt,
                                 const PackEvidence& evidence) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (HasActiveLeases())
        return Result(OperationCode::ReceiptRejected, nullptr, 0,
                      "cannot replace receipt evidence while leases are active",
                      false, LogLevel::Warning);
    const ValidationResult checked =
        ValidateReceipt(edition_, receipt, evidence);
    validation_ = checked.code;
    prepared_ = static_cast<bool>(checked);
    if (!prepared_)
        return Result(OperationCode::ReceiptRejected, nullptr, 0,
                      checked.detail, false, LogLevel::Error);
    return Result(OperationCode::Prepared, nullptr, 0,
                  enabled_ ? checked.detail
                           : checked.detail + "; host remains disabled",
                  true, LogLevel::Info);
}

OperationResult MapHost::SetEnabled(bool enabled) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (!enabled && HasActiveLeases())
        return Result(OperationCode::ActiveLeaseBlocksDisable, nullptr, 0,
                      "release every property before disabling the host",
                      false, LogLevel::Warning);
    enabled_ = enabled;
    return Result(enabled ? OperationCode::Prepared : OperationCode::Disabled,
                  nullptr, 0,
                  enabled ? "host enabled; no property was activated"
                          : "host disabled",
                  true, LogLevel::Info);
}

OperationResult MapHost::Acquire(Property property) {
    std::lock_guard<std::mutex> lock(mutex_);
    const AllowedGroup* group = FindAllowedGroup(property);
    if (group == nullptr)
        return Result(OperationCode::InvalidProperty, nullptr, 0,
                      "property is outside the compiled allowlist", false,
                      LogLevel::Warning);
    if (!enabled_)
        return Result(OperationCode::Disabled, group, 0,
                      "map host is disabled", false, LogLevel::Info);
    if (!prepared_)
        return Result(OperationCode::NotPrepared, group, 0,
                      "a verified pack receipt is required", false,
                      LogLevel::Warning);

    auto found = leases_.find(property);
    if (found != leases_.end()) {
        ++found->second.references;
        return Result(OperationCode::ReferenceAcquired, group,
                      found->second.references,
                      "existing property lease retained", true,
                      LogLevel::Debug);
    }

    std::string error;
    bool activated = false;
    try {
        activated = backend_.Acquire(*group, error);
    } catch (...) {
        error = "backend threw across its noexcept policy boundary";
    }
    if (!activated)
        return Result(OperationCode::BackendFailure, group, 0,
                      error.empty() ? "backend rejected activation" : error,
                      false, LogLevel::Error);
    leases_.emplace(property, Lease{1});
    return Result(OperationCode::Activated, group, 1,
                  "allowlisted property group activated", true,
                  LogLevel::Info);
}

OperationResult MapHost::Release(Property property, bool force) {
    std::lock_guard<std::mutex> lock(mutex_);
    const AllowedGroup* group = FindAllowedGroup(property);
    if (group == nullptr)
        return Result(OperationCode::InvalidProperty, nullptr, 0,
                      "property is outside the compiled allowlist", false,
                      LogLevel::Warning);
    const auto found = leases_.find(property);
    if (found == leases_.end())
        return Result(OperationCode::Released, group, 0,
                      "property had no active lease", true, LogLevel::Debug);

    if (!force && found->second.references > 1) {
        --found->second.references;
        return Result(OperationCode::ReferenceReleased, group,
                      found->second.references,
                      "one property reference released", true,
                      LogLevel::Debug);
    }
    if (!force && group->keep_resident)
        return Result(OperationCode::KeptResident, group,
                      found->second.references,
                      "resident yacht lease is held until shutdown", true,
                      LogLevel::Info);

    std::string error;
    bool released = false;
    try {
        released = backend_.Release(*group, error);
    } catch (...) {
        error = "backend threw across its noexcept policy boundary";
    }
    if (!released)
        return Result(OperationCode::BackendFailure, group,
                      found->second.references,
                      error.empty() ? "backend rejected release" : error,
                      false, LogLevel::Error);
    leases_.erase(found);
    return Result(OperationCode::Released, group, 0,
                  force ? "property force-released" : "property released",
                  true, LogLevel::Info);
}

bool MapHost::Shutdown() noexcept {
    std::vector<Property> properties;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        properties.reserve(leases_.size());
        for (const auto& lease : leases_) properties.push_back(lease.first);
    }
    bool complete = true;
    for (Property property : properties)
        complete = Release(property, true).success && complete;
    return complete;
}

HostSnapshot MapHost::Snapshot() const {
    std::lock_guard<std::mutex> lock(mutex_);
    HostSnapshot snapshot;
    snapshot.edition = edition_;
    snapshot.enabled = enabled_;
    snapshot.prepared = prepared_;
    snapshot.validation = validation_;
    for (const auto& item : leases_) {
        const AllowedGroup* group = FindAllowedGroup(item.first);
        if (group == nullptr) continue;
        snapshot.leases.push_back({item.first, group->property_key,
                                   group->group_name,
                                   item.second.references,
                                   group->keep_resident});
    }
    return snapshot;
}

OperationResult MapHost::Result(OperationCode code, const AllowedGroup* group,
                                std::uint32_t references, std::string detail,
                                bool success, LogLevel level) {
    logger_.Write({level,
                   code == OperationCode::ReceiptRejected
                       ? "map_host_receipt_rejected"
                       : code == OperationCode::BackendFailure
                             ? "map_host_backend_failure"
                             : code == OperationCode::Activated
                                   ? "map_host_property_activated"
                                   : code == OperationCode::Released
                                         ? "map_host_property_released"
                                         : code == OperationCode::KeptResident
                                               ? "map_host_resident_retained"
                                               : "map_host_state",
                   edition_,
                   group == nullptr ? std::string{} : group->property_key,
                   group == nullptr ? std::string{} : group->group_name,
                   references,
                   detail});
    return {code, std::move(detail), references, success};
}

bool MapHost::HasActiveLeases() const noexcept {
    return !leases_.empty();
}

}  // namespace allin1::maps
