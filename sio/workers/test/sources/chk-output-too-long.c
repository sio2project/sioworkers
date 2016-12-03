#include <stdio.h>
/* Unsafe checker that outputs first string of input. */

#define SIZE (1 << 22)
char buf[SIZE];

int main(int argc, char **argv) {
    FILE* fdo = fopen(argv[2], "r");
    fscanf(fdo, "%s", buf);
    puts("WRONG");
    puts(buf);
    return 0;
}
