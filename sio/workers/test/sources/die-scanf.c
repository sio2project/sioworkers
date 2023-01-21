#include <stdio.h>
#include <signal.h>
#include <unistd.h>

int main() {
    int a = 0;
    scanf("%d", &a);
    kill(getpid(), a);
}
