import java.util.Scanner;

public class add_print {
    static public void main(String[] args) {
        Scanner in = new Scanner(System.in);
        int a = in.nextInt();
        int b = in.nextInt();
        System.out.println(a+b);
        System.out.println("stdout");
        System.err.print("stderr");
    }
}
