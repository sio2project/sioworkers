public class procspam {
    static public void main(String[] args) {
        int n = 7348;
        int m = 43;
        for(;;) {
            n *= m;
            m %= n | 1;
        }
    }
}
