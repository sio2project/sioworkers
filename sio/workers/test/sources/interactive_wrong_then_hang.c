#include <stdio.h>
/* Prints a wrong sum and never exits */

int main() {
    int a, b;
    scanf("%d%d", &a, &b);
    printf("%d\n", a + b + 1);
    fflush(stdout);
    for(;;);
    return 0;
}
