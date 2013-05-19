#include <unistd.h>
#include <stdlib.h>

int main() {
    if (fork())
        puts("PARENT");
    else
        puts("CHILD");
    return 0;
}
