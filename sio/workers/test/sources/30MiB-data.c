#include <stdio.h>

#define SIZE 30*1024*1024
char arr[SIZE] = {1, 2, 3};

int main() {
    int a = 0;
    scanf("%d", &a);
    return arr[a];
}
