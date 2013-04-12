#include <unistd.h>

int main() {
    const char* msg = "\n";
    for(;;)
        write(1, msg, 1);
    return 0;
}
