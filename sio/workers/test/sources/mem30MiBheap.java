public class mem30MiBheap {
    // XXX: It looks like this program should consume around 20MiB,
    //      but it actually needs -Xmx30m to run!
    static final int MAXN = 20 * 1024 * 1024;
    static final int A[] = new int[MAXN / 4];

    static public void main(String[] args) {
    }
}
