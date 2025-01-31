#include <stdio.h>
#include <string.h>

int main(int argc, char *argv[]) {
    if (argc != 2) {
        printf("WRONG\nWrong number of arguments");
        return 1;
    }
    if (strcmp(argv[1], "inwer_ok") != 0) {
        printf("WRONG\nWrong test name");
        return 1;
    }
    printf("OK\n");
    return 0;
}
