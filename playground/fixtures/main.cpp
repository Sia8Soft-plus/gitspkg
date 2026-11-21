#include <demo_math.hpp>
#include <iostream>

int main() {
    const int result = demo_math::add(2, 3);
    std::cout << "2 + 3 = " << result << '\n';
    return result == 5 ? 0 : 1;
}
