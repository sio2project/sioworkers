#include <stdio.h>

int main() {
    // since sio2jail counts instructions and assumes each instruction
    // takes the same amount of time, we can just throw enough NOPs
    // in here that sio2jail will report a roughly 200ms execution time
    for (int i = 0; i < 400000; i++) {
        asm(".rept 1000 ; nop ; .endr");
    }
}
