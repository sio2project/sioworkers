#include <fcntl.h>
#include <string.h>
#include <unistd.h>

int main() {
    char buf[32];
    int fd = open("./extra_exec_file", O_RDONLY);
    read(fd, buf, sizeof(buf));
    return strcmp(buf, "DEADBEEF\n");
}
