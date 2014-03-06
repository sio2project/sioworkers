#include <stdio.h>

char line[1000];

int main() {
    FILE *f1, *f2;
    f1 = fopen("/etc/passwd", "r");
    f2 = fopen("myfile.txt", "w");
    fscanf(f1, "%s", line);
    fprintf(f2, "%s", line);
    fclose(f1);
    fclose(f2);
    return 0;
}
