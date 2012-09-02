
#include <iostream>

#ifdef __cplusplus
extern "C" {
#endif

void HelloWorld() {
    std::cout << "Hello World from cpp-lib" << std::endl;
}

#ifdef __cplusplus
}
#endif
