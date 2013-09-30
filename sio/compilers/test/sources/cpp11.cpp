/*
 * This file tests several c++11 features particulary useful during
 * programming contests.
 */

#include <unordered_map>
#include <iostream>
#include <vector>

// FEATURE TEST: variadic templates
namespace {
    const bool debug_enabled = false;

    /* Variadic template.
     * Should optimize to no-op with debug_enabled = false and -O2. */
    template <typename T>
    void debug(const T& arg1) {
        if (debug_enabled) {
            std::cerr << arg1;
        }
    }

    template <typename T, typename... R>
    void debug(const T& arg1, const R&... args) {
        debug(arg1);
        debug(args...);
    }

    template <typename... R>
    void debugln(const R&... args) {
        debug(args...);
        debug("\n");
    }
};

int main() {
    // FEATURE TEST: unordered_map + auto
    auto map = std::unordered_map<int, int>();

    // FEATURE TEST: initialization list
    std::vector<int> nums {115, 112, 97, 109, 0, -42};

    // FEATURE TEST: for
    for (auto& i: nums) {
        map[i] = i*33;
    }

    auto sum = 0LL;
    for (auto elem: map) {
        debugln("Summing ", elem.first, " => ", elem.second);
        sum += elem.second * 1000000000000LL;
    }
    std::cout << sum / 1000000000000LL << std::endl;
    return 0;
}
