#include <stdio.h>
/* Waits for more input instead of printing the sum */

int main() {
    int a, b, c;
    scanf("%d%d", &a, &b);
    scanf("%d", &c);
    printf("%d\n", a + b);
    return 0;
}
