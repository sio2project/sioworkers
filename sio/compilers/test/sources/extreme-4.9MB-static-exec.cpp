/*
 * This file should produce executable of size <5MiB but almost it.
 * Mainly when used with -O2 -static -lm
 */

#include <cstdio>
const int SIZE = 4*1024*1024;
const char BIG[SIZE] = {3};

int main(int argc, char** argv) {
    printf("%hhd", BIG[argc]);
    return 0;
}
