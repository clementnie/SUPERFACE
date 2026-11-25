`timescale 1ps/1ps

module phase5_uart_tb;
    localparam time TX_BIT = 333328;
    reg clk50 = 0;
    reg clk24 = 0;
    always #10000 clk50 = ~clk50;
    always #20833 clk24 = ~clk24;

    reg [3:0] keys = 4'b0111;
    reg [9:0] switches = 0;
    reg serial_rx = 1;
    wire serial_tx, hs, vs, ce, oe, lb, ub, we;
    wire [3:0] red, green, blue;
    wire [11:0] rgb = {red, green, blue};

    LAB8 dut (.CLOCK_50(clk50), .CLOCK_24(clk24), .KEY(keys), .SW(switches),
              .UART_RX(serial_rx), .UART_TX(serial_tx), .PS2_CLK(1'b1),
              .PS2_DAT(1'b1), .SRAM_DQ(16'hffff), .SRAM_CE_N(ce), .SRAM_OE_N(oe),
              .SRAM_LB_N(lb), .SRAM_UB_N(ub), .SRAM_WE_N(we),
              .VGA_R(red), .VGA_G(green), .VGA_B(blue), .VGA_HS(hs), .VGA_VS(vs));

    time rx_bit = 333333;
    task automatic send_byte(input byte value, input bit good_stop = 1);
        serial_rx = 0;
        #(rx_bit);
        for (int i = 0; i < 8; i++) begin
            serial_rx = value[i];
            #(rx_bit);
        end
        serial_rx = good_stop;
        #(rx_bit);
    endtask

    function automatic bit [3:0] from_hex(input byte digit);
        return (digit <= "9") ? 4'(digit - "0") : 4'(digit - "a" + 10);
    endfunction

    function automatic byte at_byte(input string hex, input int index);
        return {from_hex(hex[2*index]), from_hex(hex[2*index+1])};
    endfunction

    task automatic send(input string hex);
        for (int i = 0; i < hex.len()/2; i++)
            send_byte(at_byte(hex, i));
    endtask

    // Sample the FPGA pin with an independent UART receiver.
    byte received [0:8191];
    integer sent_count = 0, checked_count = 0, wire_frames = 0, pixel_count = 0;
    bit in_frame = 0;
    time previous_start = 0;
    time start_tick;
    byte decoded;
    initial forever begin
        @(negedge serial_tx);
        if (keys[3]) begin
            start_tick = $time;
            if (in_frame && start_tick - previous_start != 10 * TX_BIT)
                $fatal(1, "TX inserted a gap within a frame");
            previous_start = start_tick;
            #(TX_BIT / 2);
            if (serial_tx !== 0) $fatal(1, "TX start bit");
            for (int i = 0; i < 8; i++) begin
                #(TX_BIT);
                decoded[i] = serial_tx;
            end
            #(TX_BIT);
            if (serial_tx !== 1) $fatal(1, "TX stop bit");
            received[sent_count] = decoded;
            sent_count++;
            if (decoded == 8'h7e) begin
                if (in_frame) wire_frames++;
                in_frame = !in_frame;
            end
        end
    end

    task automatic expect_frame(input string hex, input string description, input time timeout);
        time deadline = $time + timeout;
        for (int i = 0; i < hex.len()/2; i++) begin
            while (checked_count == sent_count && $time < deadline)
                #1000000;
            if (checked_count == sent_count)
                $fatal(1, "Missing byte %0d: %s", i, description);
            if (received[checked_count] !== at_byte(hex, i))
                $fatal(1, "Byte %0d: %s got %02x expected %02x",
                       i, description, received[checked_count], at_byte(hex, i));
            checked_count++;
        end
    endtask

    task automatic quiet(input time duration);
        #(duration);
        if (checked_count != sent_count) $fatal(1, "Unexpected reply byte %02x", received[checked_count]);
    endtask

    task automatic reset_board;
        keys[3] = 0;
        serial_rx = 1;
        #3000000;
        keys[3] = 1;
        #3000000;
        if (serial_tx !== 1) $fatal(1, "TX idle after reset");
    endtask

    task automatic synthetic_key(input byte value);
        @(negedge clk50);
        switches[7:0] = value;
        switches[8] = 1;
        @(negedge clk50);
        switches[8] = 0;
    endtask

    // After rising VS (line 495), line 0 starts 30 complete lines later.
    // Sample away from output transitions. Read the golden strip left to right.
    task automatic check_strip(input integer y, input string palette_bytes);
        reg [15:0] expected;
        @(posedge vs);
        #(960_000_000 + y * 32_000_000 + 20_000);
        for (int i = 0; i < palette_bytes.len()/4; i++) begin
            expected = {at_byte(palette_bytes, 2*i), at_byte(palette_bytes, 2*i+1)};
            if (rgb !== expected[11:0])
                $fatal(1, "VGA y=%0d x=%0d got %h expected %h", y, i, rgb, expected[11:0]);
            pixel_count++;
            #40000;
        end
    endtask

    integer lines = 0;
    time last_hs = 0;
    always @(negedge hs) begin
        if (last_hs != 0 && keys[3] && $time - last_hs != 32_000_000)
            $fatal(1, "VGA horizontal period outside reset");
        last_hs = $time;
        lines++;
    end
    always @(negedge keys[3]) last_hs = 0;
    always @(posedge keys[3]) last_hs = 0;

    time transaction_start;
    initial begin
        `include "phase5_scenario.svh"
        if ({ce, oe, lb, ub, we} !== 5'b11111) $fatal(1, "Uninitialized SRAM was selected");
        $display("PASS %0d FPGA response frames, %0d VGA line periods, %0d RGB samples",
                 wire_frames, lines, pixel_count);
        $finish;
    end

    initial begin
        #400ms;
        $fatal(1, "Scenario watchdog");
    end
endmodule
