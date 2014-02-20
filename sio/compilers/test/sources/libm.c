/* This file checks if libm is handled correctly. */
#include <math.h>
#include <stdio.h>

int main(int argc, char **argv) {
    double v;
    sscanf(argv[1], "%lf", &v);
    printf("%lf, %lf, %lf\n", log(v), sqrt(v), atan(v));

    return 0;
}


