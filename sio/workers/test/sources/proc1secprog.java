public class proc1secprog {
    static public void main(String[] args) {
        int i = 2;
        int j = i;
        for(;i<500000000;++i)
            j += i;

        System.out.println(j-1711656321);

    }
}
