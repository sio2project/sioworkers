/*
 * This file should produce executable of >250MB
 * Even when using -O2
 */

#include <cstdio>
const int SIZE = 250*1000*1000;
const char BIG[SIZE] = {3};

int main(int argc, char** argv) {
    return BIG[argc];
}
