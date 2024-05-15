#include <stdio.h>
/* Simple unsafe checker with buffer overflow */

int main(int argc, char **argv) {
    char buf[255], buf2[255];
    FILE* fdi = fopen(argv[1], "r");
    FILE* fdo = fopen(argv[2], "r");
    FILE* fdh = fopen(argv[3], "r");
    fscanf(fdh, "%s", buf);
    fscanf(fdo, "%s", buf2);
    if (strcmp(buf, buf2) == 0)
        puts("OK\nOK\n42.00");
    else
        puts("WRONG");
    return 0;
}
