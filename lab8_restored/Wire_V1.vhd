library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

package Wire_V1 is
    subtype octet is std_logic_vector(7 downto 0);
    subtype crc_word is std_logic_vector(15 downto 0);
    constant delim : octet := x"7E";
    constant escape : octet := x"7D";
    constant hello_type : octet := x"01";
    constant extended_hello_type : octet := x"03";
    constant offer_type : octet := x"02";
    constant begin_type : octet := x"10";
    constant row_type : octet := x"11";
    constant end_type : octet := x"12";
    constant span_type : octet := x"13";
    constant cursor_type : octet := x"14";
    constant ping_type : octet := x"15";
    constant stage_span_type : octet := x"16";
    constant commit_type : octet := x"17";
    constant extended_begin_type : octet := x"18";
    constant key_type : octet := x"20";
    constant ack_type : octet := x"7F";
    function crc_byte(crc : crc_word; data : octet) return crc_word;
    type byte_array is array (natural range <>) of octet;
end package;

package body Wire_V1 is
    function crc_byte(crc : crc_word; data : octet) return crc_word is
        variable remainder : crc_word := crc xor (data & x"00");
    begin
        for bit_number in 0 to 7 loop
            if remainder(15) = '1' then
                remainder := (remainder(14 downto 0) & '0') xor x"1021";
            else
                remainder := remainder(14 downto 0) & '0';
            end if;
        end loop;
        return remainder;
    end function;

end package body;
