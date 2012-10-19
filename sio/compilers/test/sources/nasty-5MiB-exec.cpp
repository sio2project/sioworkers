/*
 * This file should produce executable of >5MiB
 * Even when using -O2
 */

#include <cstdio>
const int SIZE = 5*1024*1024;
const char BIG[SIZE] = {3};

int main(int argc, char** argv) {
    return BIG[argc];
}
