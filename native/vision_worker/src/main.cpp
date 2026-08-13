#include <algorithm>
#include <array>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <exception>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <vector>

#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

namespace {

constexpr std::array<std::byte, 4> kMagic{
    std::byte{'V'},
    std::byte{'L'},
    std::byte{'T'},
    std::byte{'1'},
};
constexpr std::uint16_t kProtocolVersion = 1;
constexpr std::size_t kHeaderSize = 28;
constexpr std::uint32_t kMaximumPayloadBytes = 1'048'576;

enum class MessageType : std::uint16_t {
    hello = 1,
    ping = 2,
    shutdown = 3,
    capabilities = 101,
    pong = 102,
    stopped = 103,
    error = 199,
};

struct Message {
    std::uint16_t type{};
    std::uint64_t sequence{};
    std::uint64_t timestamp_ns{};
    std::vector<std::byte> payload;
};

template <typename Value>
Value read_unsigned(
    const std::array<std::byte, kHeaderSize>& header,
    const std::size_t offset
) {
    static_assert(std::is_unsigned_v<Value>);
    std::uint64_t value = 0;
    for (std::size_t index = 0; index < sizeof(Value); ++index) {
        value |= static_cast<std::uint64_t>(
                     std::to_integer<unsigned int>(
                         header[offset + index]
                     )
                 )
                 << (index * 8U);
    }
    return static_cast<Value>(value);
}

template <typename Value>
void append_unsigned(std::vector<std::byte>& output, Value value) {
    static_assert(std::is_unsigned_v<Value>);
    for (std::size_t index = 0; index < sizeof(Value); ++index) {
        output.push_back(
            static_cast<std::byte>(
                (
                    static_cast<unsigned long long>(value)
                    >> (index * 8U)
                )
                & 0xFFULL
            )
        );
    }
}

bool read_exact(char* destination, const std::size_t size) {
    std::size_t received = 0;
    while (received < size) {
        std::cin.read(
            destination + received,
            static_cast<std::streamsize>(size - received)
        );
        const auto count = std::cin.gcount();
        if (count <= 0) {
            return false;
        }
        received += static_cast<std::size_t>(count);
    }
    return true;
}

Message read_message() {
    std::array<std::byte, kHeaderSize> header{};
    if (!read_exact(
            reinterpret_cast<char*>(header.data()),
            header.size()
        )) {
        throw std::runtime_error("command stream closed");
    }
    if (!std::equal(kMagic.begin(), kMagic.end(), header.begin())) {
        throw std::runtime_error("invalid protocol magic");
    }
    const auto version = read_unsigned<std::uint16_t>(header, 4);
    if (version != kProtocolVersion) {
        throw std::runtime_error("unsupported protocol version");
    }
    const auto payload_size = read_unsigned<std::uint32_t>(header, 8);
    if (payload_size > kMaximumPayloadBytes) {
        throw std::runtime_error("payload exceeds configured limit");
    }
    Message message{
        .type = read_unsigned<std::uint16_t>(header, 6),
        .sequence = read_unsigned<std::uint64_t>(header, 12),
        .timestamp_ns = read_unsigned<std::uint64_t>(header, 20),
        .payload = std::vector<std::byte>(
            static_cast<std::size_t>(payload_size)
        ),
    };
    if (
        payload_size > 0
        && !read_exact(
            reinterpret_cast<char*>(message.payload.data()),
            message.payload.size()
        )
    ) {
        throw std::runtime_error("payload is truncated");
    }
    return message;
}

std::uint64_t monotonic_nanoseconds() {
    return static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::steady_clock::now().time_since_epoch()
        )
            .count()
    );
}

void write_message(
    const MessageType type,
    const std::uint64_t sequence,
    const std::string& payload = {}
) {
    if (payload.size() > kMaximumPayloadBytes) {
        throw std::runtime_error("response payload exceeds configured limit");
    }
    std::vector<std::byte> output;
    output.reserve(kHeaderSize + payload.size());
    output.insert(output.end(), kMagic.begin(), kMagic.end());
    append_unsigned(output, kProtocolVersion);
    append_unsigned(output, static_cast<std::uint16_t>(type));
    append_unsigned(output, static_cast<std::uint32_t>(payload.size()));
    append_unsigned(output, sequence);
    append_unsigned(output, monotonic_nanoseconds());
    for (const char item : payload) {
        output.push_back(static_cast<std::byte>(item));
    }
    std::cout.write(
        reinterpret_cast<const char*>(output.data()),
        static_cast<std::streamsize>(output.size())
    );
    std::cout.flush();
    if (!std::cout) {
        throw std::runtime_error("response stream closed");
    }
}

void configure_binary_stdio() {
#ifdef _WIN32
    if (
        _setmode(_fileno(stdin), _O_BINARY) == -1
        || _setmode(_fileno(stdout), _O_BINARY) == -1
    ) {
        throw std::runtime_error("could not configure binary standard I/O");
    }
#endif
}

int run() {
    configure_binary_stdio();
    bool handshake_complete = false;
    while (true) {
        const Message message = read_message();
        const auto type = static_cast<MessageType>(message.type);
        if (!handshake_complete && type != MessageType::hello) {
            write_message(
                MessageType::error,
                message.sequence,
                "hello must be the first command"
            );
            continue;
        }
        switch (type) {
        case MessageType::hello:
            handshake_complete = true;
            write_message(
                MessageType::capabilities,
                message.sequence,
                R"({"name":"vulture-vision-worker","protocol_version":1,"features":["ping","shutdown"]})"
            );
            break;
        case MessageType::ping:
            write_message(MessageType::pong, message.sequence);
            break;
        case MessageType::shutdown:
            write_message(MessageType::stopped, message.sequence);
            return 0;
        default:
            write_message(
                MessageType::error,
                message.sequence,
                "unsupported command"
            );
            break;
        }
    }
}

}  // namespace

int main() {
    try {
        return run();
    } catch (const std::exception& error) {
        std::cerr << "vulture-vision-worker: " << error.what() << '\n';
        return 2;
    }
}
