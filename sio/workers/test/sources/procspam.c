#include <unistd.h>

int main() {
    int n = 7348;
    int m = 43;
    for(;;) {
        n *= m;
        m %= n | 1;
    }
    return 0;
}
