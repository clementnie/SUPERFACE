`timescale 1ps/1ps

module phase5_phy_tb;
    localparam time BIT = 333328;
    reg clk50 = 0, clk24 = 0;
    always #10000 clk50 = ~clk50;
    always #20833 clk24 = ~clk24;

    reg board_reset = 1, serial_rx = 1, rx_pop = 0, tx_push = 0;
    reg [8:0] tx_token = 0;
    wire serial_tx, rx_empty, tx_full, frame_done, reset50, run50;
    wire overflow_seen, starvation_seen, framing_seen;
    wire [8:0] rx_token;
    wire framing_error = rx_pop && !rx_empty && rx_token[8];

    UART_PHY dut (.*);

    task automatic input_byte(input byte value, input time bit_period, input bit stop = 1);
        serial_rx = 0;
        #(bit_period);
        for (int i = 0; i < 8; i++) begin
            serial_rx = value[i];
            #(bit_period);
        end
        serial_rx = stop;
        #(bit_period);
    endtask

    task automatic take(input logic [8:0] expected);
        wait (!rx_empty);
        @(negedge clk50);
        if (rx_token !== expected) $fatal(1, "RX token got %03x expected %03x", rx_token, expected);
        rx_pop = 1;
        @(negedge clk50);
        rx_pop = 0;
    endtask

    task automatic offer(input logic [8:0] value);
        @(negedge clk50);
        while (tx_full) @(negedge clk50);
        tx_push = 1;
        tx_token = value;
        @(negedge clk50);
        tx_push = 0;
    endtask

    task automatic output_byte(input byte expected, output time began);
        byte value;
        @(negedge serial_tx);
        began = $time;
        #(BIT/2);
        if (serial_tx !== 0) $fatal(1, "TX start");
        for (int j = 0; j < 8; j++) begin
            #(BIT);
            value[j] = serial_tx;
        end
        #(BIT);
        if (serial_tx !== 1 || value !== expected) $fatal(1, "TX got %h expected %h", value, expected);
    endtask

    initial begin
        #1_000_000;
        board_reset = 0;
        wait (run50);
        serial_rx = 0;
        #(BIT/4);
        serial_rx = 1;
        #(2*BIT);
        if (!rx_empty) $fatal(1, "Glitch triggered a token");
        input_byte(8'h00, BIT, 0);
        serial_rx = 1;
        #(BIT);
        take(9'h100);
        if (!framing_seen) $fatal(1, "Framing marker not visible");

        for (int i = 0; i < 16; i++) input_byte(8'h40 + 8'(i), 327000);
        if (overflow_seen) $fatal(1, "16 entries did not fit");
        for (int i = 0; i < 16; i++) take(9'h040 + 9'(i));
        #1_000_000;
        if (!rx_empty) $fatal(1, "RX did not return empty");

        fork
            begin
                for (int i = 0; i < 32; i++) input_byte(8'(i ^ 8'ha5), 339000);
            end
            begin
                for (int i = 0; i < 32; i++) take(9'(i ^ 8'ha5));
            end
            begin
                for (int i = 0; i < 32; i++) offer({i == 31, 8'(i ^ 8'h5a)});
            end
            begin
                time mark, prior;
                for (int i = 0; i < 32; i++) begin
                    output_byte(8'(i ^ 8'h5a), mark);
                    if (i > 0 && mark - prior != 10*BIT)
                        $fatal(1, "TX wire gap");
                    prior = mark;
                end
                @(posedge frame_done);
                if ($time < mark + 10*BIT) $fatal(1, "Premature TX frame done");
            end
        join
        if (overflow_seen || starvation_seen) $fatal(1, "Unexpected concurrent PHY fault");

        for (int i = 0; i < 17; i++) input_byte(8'ha5, BIT);
        if (!overflow_seen) $fatal(1, "RX overflow was not reported");
        wait (run50);
        #(12*BIT);
        input_byte(8'h55, BIT);
        take(9'h055);

        for (int i = 0; i < 8; i++) offer(9'h05a);
        wait (starvation_seen);
        wait (run50);
        if (serial_tx !== 1) $fatal(1, "Starvation recovery did not return idle");
        $display("PASS PHY timing and margins, FIFO boundary, ordered framing token, full duplex, overflow and starvation recovery");
        $finish;
    end

    initial begin
        #1_000_000_000;
        $fatal(1, "PHY test watchdog");
    end
endmodule
