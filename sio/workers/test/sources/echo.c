#include <stdio.h>

int main()
{
	char c;
	do
	{
		c = getchar();
		if (c != EOF)
			putchar(c);
	} while (c != EOF);
	return 0;
}