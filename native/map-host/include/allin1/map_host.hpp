#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <map>
#include <mutex>
#include <string>
#include <vector>

namespace allin1::maps {

inline constexpr std::uint32_t kMapHostAbiVersion = 1;
inline constexpr const char* kExpectedPackageId = "allin1.online-content";
inline constexpr const char* kExpectedPackName = "allin1_maps";
inline constexpr const char* kExpectedLayout = "pruned-local-v3-deferred";
inline constexpr const char* kExpectedArchiveRegistration = "property-groups";
inline constexpr const char* kExpectedActivation =
    "property-group-native-host-required";

enum class Edition : std::uint8_t {
    Legacy = 1,
    Enhanced = 2,
};

enum class Property : std::uint8_t {
    Grapeseed = 1,
    Yacht = 2,
    Davis = 3,
    Harmony = 4,
    Paleto = 5,
    GarmentFactory = 6,
};

struct AllowedGroup {
    Property property;
    const char* property_key;
    const char* group_name;
    const char* changeset_name;
    bool keep_resident;
};

// The launcher/installer owns JSON and filesystem parsing. The native policy
// boundary accepts only this bounded, typed representation. It never accepts a
// caller-supplied native hash or an unrecognized content group name.
struct ReceiptGroup {
    Property property;
    std::string property_key;
    std::string group_name;
    std::string changeset_name;
};

struct PackReceipt {
    std::uint32_t schema = 0;
    std::string status;
    std::string package_id;
    std::string pack_name;
    std::string layout;
    Edition edition = Edition::Legacy;
    std::uint64_t archive_bytes = 0;
    std::string archive_sha256;
    std::vector<ReceiptGroup> groups;
};

// Evidence is independently collected from the installed pack. Receipt data
// alone is insufficient: its archive identity must agree with the observed
// file and with the installer marker before the host can become ready.
struct PackEvidence {
    std::string marker_layout;
    std::string marker_archive_registration;
    std::string marker_activation;
    std::uint64_t actual_archive_bytes = 0;
    std::string actual_archive_sha256;
};

enum class ValidationCode : std::uint8_t {
    Valid = 0,
    InvalidSchema,
    InvalidStatus,
    WrongPackage,
    WrongPack,
    WrongLayout,
    WrongEdition,
    InvalidArchiveIdentity,
    MarkerMismatch,
    MissingGroup,
    DuplicateGroup,
    UnknownGroup,
    GroupMismatch,
};

struct ValidationResult {
    ValidationCode code = ValidationCode::Valid;
    std::string detail;
    explicit operator bool() const noexcept {
        return code == ValidationCode::Valid;
    }
};

enum class LogLevel : std::uint8_t {
    Debug,
    Info,
    Warning,
    Error,
};

struct LogEvent {
    LogLevel level = LogLevel::Info;
    std::string code;
    Edition edition = Edition::Legacy;
    std::string property_key;
    std::string group_name;
    std::uint32_t reference_count = 0;
    std::string detail;
};

class ILogger {
public:
    virtual ~ILogger() = default;
    virtual void Write(const LogEvent& event) noexcept = 0;
};

// This is the only activation boundary. Implementations receive a descriptor
// selected from the compiled allowlist; no public method accepts a group hash.
// The canonical Legacy/Gen9 ABI is verified, but it operates globally by group
// hash. The production implementation remains deliberately absent until the
// registered-pack route passes a live isolation canary on each edition.
class IMapGroupBackend {
public:
    virtual ~IMapGroupBackend() = default;
    virtual bool Acquire(const AllowedGroup& group,
                         std::string& error) noexcept = 0;
    virtual bool Release(const AllowedGroup& group,
                         std::string& error) noexcept = 0;
};

struct HostOptions {
    // Activation is opt-in. Constructing, preparing, or loading the host never
    // activates a map group.
    bool enabled = false;
};

enum class OperationCode : std::uint8_t {
    Prepared,
    Disabled,
    NotPrepared,
    ReceiptRejected,
    InvalidProperty,
    Activated,
    ReferenceAcquired,
    ReferenceReleased,
    Released,
    KeptResident,
    BackendFailure,
    ActiveLeaseBlocksDisable,
};

struct OperationResult {
    OperationCode code = OperationCode::NotPrepared;
    std::string detail;
    std::uint32_t reference_count = 0;
    bool success = false;
};

struct LeaseSnapshot {
    Property property = Property::Grapeseed;
    std::string property_key;
    std::string group_name;
    std::uint32_t reference_count = 0;
    bool keep_resident = false;
};

struct HostSnapshot {
    std::uint32_t abi_version = kMapHostAbiVersion;
    Edition edition = Edition::Legacy;
    bool enabled = false;
    bool prepared = false;
    ValidationCode validation = ValidationCode::Valid;
    std::vector<LeaseSnapshot> leases;
};

const std::array<AllowedGroup, 6>& Allowlist() noexcept;
const AllowedGroup* FindAllowedGroup(Property property) noexcept;
const char* EditionName(Edition edition) noexcept;
ValidationResult ValidateReceipt(Edition expected_edition,
                                 const PackReceipt& receipt,
                                 const PackEvidence& evidence);

class MapHost final {
public:
    MapHost(Edition edition, IMapGroupBackend& backend, ILogger& logger,
            HostOptions options = {});

    // Prepare validates identity and allowlist coverage only. It makes zero
    // backend calls, which is a tested no-startup-activation invariant.
    OperationResult Prepare(const PackReceipt& receipt,
                            const PackEvidence& evidence);
    OperationResult SetEnabled(bool enabled);
    OperationResult Acquire(Property property);
    OperationResult Release(Property property, bool force = false);
    bool Shutdown() noexcept;
    HostSnapshot Snapshot() const;

private:
    struct Lease {
        std::uint32_t references = 0;
    };

    OperationResult Result(OperationCode code, const AllowedGroup* group,
                           std::uint32_t references, std::string detail,
                           bool success, LogLevel level);
    bool HasActiveLeases() const noexcept;

    Edition edition_;
    IMapGroupBackend& backend_;
    ILogger& logger_;
    bool enabled_;
    bool prepared_ = false;
    ValidationCode validation_ = ValidationCode::Valid;
    std::map<Property, Lease> leases_;
    mutable std::mutex mutex_;
};

}  // namespace allin1::maps
