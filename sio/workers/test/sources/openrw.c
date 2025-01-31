#include <fcntl.h>
#include <unistd.h>

int main() {
    char ch[] = "1337";
    int fd = open("./somefile", O_RDWR);
    int fd2 = open("./not_existing", O_WRONLY | O_CREAT, 0200);
    int wr = write(fd, ch, 2);
    int wr2 = write(fd2, ch, 2);

    return !(wr == 2 && wr2 == 2);
}
