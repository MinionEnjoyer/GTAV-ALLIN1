// Small, dependency-free JSON reader for security-sensitive launcher state.
// It intentionally exposes only the CLR shapes consumed by ExtensionRuntime:
// Dictionary<string, object>, object[], string, numeric values, bool, and null.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;

namespace ALLIN1
{
    internal sealed class PortableJsonParser
    {
        internal const int MaximumJsonLength = 4 * 1024 * 1024;
        internal const int MaximumDepth = 64;
        internal const int MaximumValueCount = 262144;

        private readonly string _json;
        private int _position;
        private int _valueCount;

        private PortableJsonParser(string json)
        {
            _json = json;
        }

        internal static object Parse(string json)
        {
            return Parse(json, MaximumJsonLength);
        }

        internal static object Parse(string json, int maximumJsonLength)
        {
            if (json == null)
                throw new InvalidDataException("JSON input is null");
            if (maximumJsonLength < 1 || json.Length > maximumJsonLength)
                throw new InvalidDataException("JSON input exceeds its length limit");

            var parser = new PortableJsonParser(json);
            parser.SkipWhitespace();
            object value = parser.ParseValue(0);
            parser.SkipWhitespace();
            if (!parser.AtEnd)
                parser.Fail("Unexpected trailing content");
            return value;
        }

        private bool AtEnd => _position >= _json.Length;

        private object ParseValue(int depth)
        {
            if (AtEnd) Fail("Expected a JSON value");
            _valueCount++;
            if (_valueCount > MaximumValueCount)
                Fail("JSON input exceeds its value limit");

            switch (_json[_position])
            {
                case '{': return ParseObject(depth);
                case '[': return ParseArray(depth);
                case '"': return ParseString();
                case 't': ReadLiteral("true"); return true;
                case 'f': ReadLiteral("false"); return false;
                case 'n': ReadLiteral("null"); return null;
                default:
                    if (_json[_position] == '-' || IsDigit(_json[_position]))
                        return ParseNumber();
                    Fail("Expected a JSON value");
                    return null;
            }
        }

        private Dictionary<string, object> ParseObject(int depth)
        {
            EnsureContainerDepth(depth);
            _position++;
            SkipWhitespace();
            var result = new Dictionary<string, object>(StringComparer.Ordinal);
            if (Consume('}')) return result;

            while (true)
            {
                if (AtEnd || _json[_position] != '"')
                    Fail("Expected an object member name");
                string key = ParseString();
                if (result.ContainsKey(key))
                    Fail("Duplicate object member: " + key);
                SkipWhitespace();
                Expect(':');
                SkipWhitespace();
                object value = ParseValue(depth + 1);
                result.Add(key, value);
                SkipWhitespace();
                if (Consume('}')) return result;
                Expect(',');
                SkipWhitespace();
            }
        }

        private object[] ParseArray(int depth)
        {
            EnsureContainerDepth(depth);
            _position++;
            SkipWhitespace();
            var result = new List<object>();
            if (Consume(']')) return result.ToArray();

            while (true)
            {
                result.Add(ParseValue(depth + 1));
                SkipWhitespace();
                if (Consume(']')) return result.ToArray();
                Expect(',');
                SkipWhitespace();
            }
        }

        private string ParseString()
        {
            Expect('"');
            var result = new StringBuilder();
            while (!AtEnd)
            {
                char value = _json[_position++];
                if (value == '"') return result.ToString();
                if (value == '\\')
                {
                    AppendEscape(result);
                    continue;
                }
                if (value < 0x20)
                    Fail("Unescaped control character in string");
                if (char.IsHighSurrogate(value))
                {
                    if (AtEnd || !char.IsLowSurrogate(_json[_position]))
                        Fail("Invalid Unicode surrogate pair");
                    result.Append(value);
                    result.Append(_json[_position++]);
                    continue;
                }
                if (char.IsLowSurrogate(value))
                    Fail("Invalid Unicode surrogate pair");
                result.Append(value);
            }
            Fail("Unterminated string");
            return null;
        }

        private void AppendEscape(StringBuilder result)
        {
            if (AtEnd) Fail("Unterminated string escape");
            char escaped = _json[_position++];
            switch (escaped)
            {
                case '"': result.Append('"'); return;
                case '\\': result.Append('\\'); return;
                case '/': result.Append('/'); return;
                case 'b': result.Append('\b'); return;
                case 'f': result.Append('\f'); return;
                case 'n': result.Append('\n'); return;
                case 'r': result.Append('\r'); return;
                case 't': result.Append('\t'); return;
                case 'u':
                    char codeUnit = ReadHexCodeUnit();
                    if (char.IsHighSurrogate(codeUnit))
                    {
                        if (_position + 1 >= _json.Length ||
                            _json[_position] != '\\' ||
                            _json[_position + 1] != 'u')
                            Fail("Invalid Unicode surrogate pair");
                        _position += 2;
                        char low = ReadHexCodeUnit();
                        if (!char.IsLowSurrogate(low))
                            Fail("Invalid Unicode surrogate pair");
                        result.Append(codeUnit);
                        result.Append(low);
                        return;
                    }
                    if (char.IsLowSurrogate(codeUnit))
                        Fail("Invalid Unicode surrogate pair");
                    result.Append(codeUnit);
                    return;
                default:
                    Fail("Invalid string escape");
                    return;
            }
        }

        private char ReadHexCodeUnit()
        {
            if (_position + 4 > _json.Length)
                Fail("Incomplete Unicode escape");
            int value = 0;
            for (int index = 0; index < 4; index++)
            {
                int digit = HexValue(_json[_position++]);
                if (digit < 0) Fail("Invalid Unicode escape");
                value = (value << 4) | digit;
            }
            return (char)value;
        }

        private object ParseNumber()
        {
            int start = _position;
            Consume('-');
            if (AtEnd) Fail("Incomplete number");

            if (Consume('0'))
            {
                if (!AtEnd && IsDigit(_json[_position]))
                    Fail("Leading zero in number");
            }
            else
            {
                if (AtEnd || !IsNonzeroDigit(_json[_position]))
                    Fail("Invalid number");
                do { _position++; }
                while (!AtEnd && IsDigit(_json[_position]));
            }

            bool fractional = false;
            if (Consume('.'))
            {
                fractional = true;
                if (AtEnd || !IsDigit(_json[_position]))
                    Fail("Invalid fraction");
                do { _position++; }
                while (!AtEnd && IsDigit(_json[_position]));
            }

            if (!AtEnd && (_json[_position] == 'e' || _json[_position] == 'E'))
            {
                fractional = true;
                _position++;
                if (!AtEnd && (_json[_position] == '+' || _json[_position] == '-'))
                    _position++;
                if (AtEnd || !IsDigit(_json[_position]))
                    Fail("Invalid exponent");
                do { _position++; }
                while (!AtEnd && IsDigit(_json[_position]));
            }

            string token = _json.Substring(start, _position - start);
            if (!fractional)
            {
                int integer;
                if (int.TryParse(token, NumberStyles.AllowLeadingSign,
                    CultureInfo.InvariantCulture, out integer))
                    return integer;
                long longInteger;
                if (long.TryParse(token, NumberStyles.AllowLeadingSign,
                    CultureInfo.InvariantCulture, out longInteger))
                    return longInteger;
            }

            decimal decimalNumber;
            if (decimal.TryParse(token, NumberStyles.Float,
                CultureInfo.InvariantCulture, out decimalNumber))
                return decimalNumber;
            double doubleNumber;
            if (double.TryParse(token, NumberStyles.Float,
                    CultureInfo.InvariantCulture, out doubleNumber) &&
                !double.IsInfinity(doubleNumber) && !double.IsNaN(doubleNumber))
                return doubleNumber;
            Fail("Number is outside the supported range");
            return null;
        }

        private void ReadLiteral(string literal)
        {
            if (_position + literal.Length > _json.Length ||
                string.CompareOrdinal(_json, _position, literal, 0,
                    literal.Length) != 0)
                Fail("Invalid JSON literal");
            _position += literal.Length;
        }

        private void EnsureContainerDepth(int depth)
        {
            if (depth >= MaximumDepth)
                Fail("JSON input exceeds its nesting limit");
        }

        private void SkipWhitespace()
        {
            while (!AtEnd)
            {
                char value = _json[_position];
                if (value != ' ' && value != '\t' && value != '\r' && value != '\n')
                    return;
                _position++;
            }
        }

        private bool Consume(char expected)
        {
            if (AtEnd || _json[_position] != expected) return false;
            _position++;
            return true;
        }

        private void Expect(char expected)
        {
            if (!Consume(expected)) Fail("Expected '" + expected + "'");
        }

        private void Fail(string message)
        {
            throw new InvalidDataException(
                message + " at JSON character " + _position.ToString(
                    CultureInfo.InvariantCulture));
        }

        private static bool IsDigit(char value)
        {
            return value >= '0' && value <= '9';
        }

        private static bool IsNonzeroDigit(char value)
        {
            return value >= '1' && value <= '9';
        }

        private static int HexValue(char value)
        {
            if (value >= '0' && value <= '9') return value - '0';
            if (value >= 'a' && value <= 'f') return value - 'a' + 10;
            if (value >= 'A' && value <= 'F') return value - 'A' + 10;
            return -1;
        }
    }
}
