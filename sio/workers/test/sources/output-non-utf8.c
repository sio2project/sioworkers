#include <unistd.h>

int main() {
    char buf[256];
    int i = 0;
    for (i=250; i>=0; i--)
        buf[i] = (char) 255-i;
    write(1, buf, sizeof(buf));
    return 0;
}
