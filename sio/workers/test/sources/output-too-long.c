#include <string.h>
#include <unistd.h>

#define SIZE (1 << 20)
char bytes[SIZE];

int main() {
    memset(bytes, 'X', SIZE - 1);
    bytes[SIZE - 1] = '\n';
    write(1, bytes, SIZE);
    return 0;
}
