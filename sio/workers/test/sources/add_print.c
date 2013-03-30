#include <stdio.h>

int main() {
    int a,b;
    scanf("%d%d", &a, &b);
    printf("%d\nstdout\n", a+b);
    fprintf(stderr, "stderr");
    return 0;
}
