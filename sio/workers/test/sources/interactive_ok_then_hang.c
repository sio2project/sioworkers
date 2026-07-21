#include <stdio.h>
/* Prints the correct sum but never exits */

int main() {
    int a, b;
    scanf("%d%d", &a, &b);
    printf("%d\n", a + b);
    fflush(stdout);
    for(;;);
    return 0;
}
