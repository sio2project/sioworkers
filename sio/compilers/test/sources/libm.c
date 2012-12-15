/* This file checks if libm is handled correctly. */
#include <math.h>
#include <stdio.h>

int main() {
    double v = 999.412;

    printf("%lf, %lf, %lf\n", log(v), sqrt(v), atan(v));

    return 0;
}


