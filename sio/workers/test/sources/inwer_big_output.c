#include <stdio.h>
#define MIN_N 0
#define MAX_N 1000
#define OUTPUT 100

int main() {
    int n, i;
    scanf("%d", &n);
    if(n < MIN_N || n > MAX_N) {
        printf("WRONG\tn = %d is outside of range [%d, %d]", n, MIN_N, MAX_N);
        return 1;
    }
    for(i = 0; i < OUTPUT; i++) {
        printf("A");
    }
    printf("OK\n");
    return 0;
}
