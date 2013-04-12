#include <stdio.h>
#include <stdlib.h>

const int MAXN = 30 * 1024 * 1024;

int main() {
    int a;
    scanf("%d", &a);
    char* s = malloc(MAXN);
    s[a] = 0;
    s[MAXN-1] = 0;
    return s[a];
}
