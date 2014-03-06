#include <stdio.h>
#define FILES_NUM 5
#define MAX_LEN 100

void write_file(const char *name, const char *content) {
    FILE *out_file;
    out_file = fopen(name, "w");
    fprintf(out_file, "%s\n", content);
    fclose(out_file);
}

char files[FILES_NUM][2][MAX_LEN] = {
    {"one.txt", "1"},
    {"two.upload", "2"},
    {"three_upload", "3"},
    {"upload.four", "4"},
    {"five.five.upload", "5"},
};

int main() {
    int i;
    for(i = 0; i < FILES_NUM; i++)
        write_file(files[i][0], files[i][1]);
    printf("Everything OK\nReally");
    return 0;
}
