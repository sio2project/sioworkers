#include <stdio.h>
#include <limits.h>

int main() {
    int i = 2;
    int j = i;

    // runtime (wall time) on various machines:
    // * my workstation (Ryzen 9 5900X): ~1.5s
    // * a dedicated judging machine (Xeon E5530): ~5.5s
    for (; i < INT_MAX; i++) {
        j += i;
    }

    printf("%d\n", j - 1073741826);

    return 0;
}
