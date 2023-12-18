#include <cassert>
#include <cstdio>
#include <cstdlib>

using namespace std;

int main(int argc, char **argv) {
	assert(argc == 5);

	FILE *in = fopen(argv[1], "r");
	assert(in);
	FILE *hint = fopen(argv[2], "r");
	assert(hint);
	FILE *channel_out = fopen(argv[3], "r");
	assert(channel_out);
	FILE *encoder_out = fopen(argv[4], "r");
	assert(encoder_out);

	assert(fseek(in, 2, SEEK_SET) >= 0);

	int ch;
	while ((ch = fgetc(encoder_out)) != EOF) {
		if (fgetc(in) != ch) {
			puts("WA\nZły wynik\n0");
			return 0;
		}
	}
	if (fgetc(in) != EOF) puts("WA\nZły wynik\n0");

	puts("OK\nBardzo dobrze\n100");

	fclose(in);
	fclose(hint);
	fclose(channel_out);
	fclose(encoder_out);
}
