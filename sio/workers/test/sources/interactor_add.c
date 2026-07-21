#include <stdio.h>
#include <stdlib.h>
/* Interactor which sends two numbers to the solution and expects
   their sum back */

int main(int argc, char **argv) {
    FILE* fin = fdopen(atoi(argv[2]), "r");
    FILE* fout = fdopen(atoi(argv[3]), "w");
    int a, b, sum;
    scanf("%d%d", &a, &b);
    fprintf(fout, "%d %d\n", a, b);
    fflush(fout);
    if (fscanf(fin, "%d", &sum) != 1) {
        puts("WRONG\ngot no output");
        return 0;
    }
    if (sum == a + b)
        puts("OK\nOK\n100");
    else
        puts("WRONG\nbad answer");
    return 0;
}
