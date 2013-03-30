#include <unistd.h>
#include <string.h>

char s[1024*1024];
int main() {
    memset(s, 0x0a, sizeof(s));
    for(;;)
        write(1, s, sizeof(s));
    return 0;
}
