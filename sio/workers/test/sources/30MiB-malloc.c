#include <stdio.h>
#include <stdlib.h>

const int MAXN = 30 * 1024 * 1024;

int main() {
    int a;
    scanf("%d", &a);
    volatile char* s = malloc(MAXN); // volatile to prevent the compiler from optimizing malloc out.
    s[a] = 0;
    s[MAXN-1] = 0;
    return s[a];
}
