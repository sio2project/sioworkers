#include <cassert>
#include <cstdio>
#include <cstdlib>

using namespace std;

int main(int argc, char **argv) {
	assert(argc == 6);

	FILE *in = fopen(argv[1], "r");
	assert(in);
	FILE *out = fopen(argv[2], "r");
	assert(out);
	FILE *hint = fopen(argv[3], "r");
	assert(hint);
	FILE *result = fdopen(atoi(argv[4]), "w");
	assert(result);
	FILE *checker = fdopen(atoi(argv[5]), "w");
	assert(checker);

	fputs("D\n", result);

	int ch;
	while ((ch = fgetc(out)) != EOF) {
		if (fgetc(hint) != ch) {
			puts("WA\nZły wynik\n0");
			return 0;
		}

		assert(fputc(ch, result) != EOF);
	}

	assert(fputs("OK\n", checker) != EOF);

	puts("OK\nBardzo dobrze\n100");

	fclose(in);
	fclose(out);
	fclose(hint);
	fclose(result);
	fclose(checker);
}
