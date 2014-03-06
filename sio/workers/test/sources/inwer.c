#include <stdio.h>
#define MIN_N 0
#define MAX_N 1000

int main() {
    int n;
    scanf("%d", &n);
    if(n < MIN_N || n > MAX_N) {
        printf("WRONG\tn = %d is outside of range [%d, %d]", n, MIN_N, MAX_N);
        return 1;
    }
    printf("OK\n");
    return 0;
}
