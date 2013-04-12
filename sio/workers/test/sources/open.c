#include <fcntl.h>

int main() {
    int ch[2];
    int fd = open("./exe", O_RDONLY);
    return read(fd, ch, 2) <= 0;
}
