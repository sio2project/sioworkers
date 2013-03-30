#include <stdio.h>
const int MAXN = 30 * 1024 * 1024;


int fun(int i) {
    char ARRAY[MAXN];
    ARRAY[1] = 99;
    ARRAY[i] = i;
    ARRAY[i^2*i] = i*33*i;
    return ARRAY[((i>>1)<<1)^i];
}


int main() {
    int a;
    scanf("%d", &a);
    printf("%d\n", fun(a));
    return 0;
}

