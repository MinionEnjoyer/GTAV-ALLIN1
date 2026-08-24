using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;

namespace RealisticSuppressors
{
    /// <summary>
    /// Small dependency-free JSON codec for the ScriptHookVDotNet host. It
    /// keeps state and diagnostics independent of host-specific System.Web
    /// framework internals across Legacy, Enhanced, and test runtimes.
    /// </summary>
    internal static class PortableJson
    {
        private const int MaximumLength = 4 * 1024 * 1024;
        private const int MaximumDepth = 64;

        internal static Dictionary<string, object> ParseObject(string json)
        {
            object value = Parse(json);
            if (value is Dictionary<string, object> result)
                return result;
            throw new InvalidDataException("JSON root must be an object.");
        }

        internal static object Parse(string json)
        {
            if (json == null)
                throw new ArgumentNullException(nameof(json));
            if (json.Length > MaximumLength)
                throw new InvalidDataException("JSON exceeds the size limit.");
            return new Reader(json).ReadDocument();
        }

        internal static string Serialize(object value)
        {
            var output = new StringBuilder();
            WriteValue(output, value, 0);
            if (output.Length > MaximumLength)
                throw new InvalidDataException("JSON exceeds the size limit.");
            return output.ToString();
        }

        private static void WriteValue(
            StringBuilder output, object value, int depth)
        {
            if (depth > MaximumDepth)
                throw new InvalidDataException("JSON exceeds the depth limit.");
            if (value == null)
            {
                output.Append("null");
                return;
            }
            if (value is string text)
            {
                WriteString(output, text);
                return;
            }
            if (value is char character)
            {
                WriteString(output, character.ToString());
                return;
            }
            if (value is bool boolean)
            {
                output.Append(boolean ? "true" : "false");
                return;
            }
            if (IsNumber(value))
            {
                WriteNumber(output, value);
                return;
            }
            if (value is IDictionary dictionary)
            {
                output.Append('{');
                bool first = true;
                foreach (DictionaryEntry entry in dictionary)
                {
                    if (!(entry.Key is string key))
                        throw new InvalidDataException(
                            "JSON object keys must be strings.");
                    if (!first) output.Append(',');
                    first = false;
                    WriteString(output, key);
                    output.Append(':');
                    WriteValue(output, entry.Value, depth + 1);
                }
                output.Append('}');
                return;
            }
            if (value is IEnumerable sequence)
            {
                output.Append('[');
                bool first = true;
                foreach (object item in sequence)
                {
                    if (!first) output.Append(',');
                    first = false;
                    WriteValue(output, item, depth + 1);
                }
                output.Append(']');
                return;
            }
            throw new InvalidDataException(
                "Unsupported JSON value type: " + value.GetType().FullName);
        }

        private static bool IsNumber(object value) =>
            value is byte || value is sbyte || value is short ||
            value is ushort || value is int || value is uint ||
            value is long || value is ulong || value is float ||
            value is double || value is decimal;

        private static void WriteNumber(StringBuilder output, object value)
        {
            if (value is float single)
            {
                if (float.IsNaN(single) || float.IsInfinity(single))
                    throw new InvalidDataException(
                        "JSON numbers must be finite.");
                output.Append(single.ToString("R", CultureInfo.InvariantCulture));
                return;
            }
            if (value is double number)
            {
                if (double.IsNaN(number) || double.IsInfinity(number))
                    throw new InvalidDataException(
                        "JSON numbers must be finite.");
                output.Append(number.ToString("R", CultureInfo.InvariantCulture));
                return;
            }
            output.Append(Convert.ToString(value, CultureInfo.InvariantCulture));
        }

        private static void WriteString(StringBuilder output, string value)
        {
            output.Append('"');
            foreach (char character in value ?? "")
            {
                switch (character)
                {
                    case '"': output.Append("\\\""); break;
                    case '\\': output.Append("\\\\"); break;
                    case '\b': output.Append("\\b"); break;
                    case '\f': output.Append("\\f"); break;
                    case '\n': output.Append("\\n"); break;
                    case '\r': output.Append("\\r"); break;
                    case '\t': output.Append("\\t"); break;
                    default:
                        if (character < 0x20)
                        {
                            output.Append("\\u");
                            output.Append(((int)character).ToString(
                                "X4", CultureInfo.InvariantCulture));
                        }
                        else output.Append(character);
                        break;
                }
            }
            output.Append('"');
        }

        private sealed class Reader
        {
            private readonly string _json;
            private int _index;

            internal Reader(string json)
            {
                _json = json;
            }

            internal object ReadDocument()
            {
                SkipWhitespace();
                object value = ReadValue(0);
                SkipWhitespace();
                if (_index != _json.Length)
                    Fail("Unexpected trailing content.");
                return value;
            }

            private object ReadValue(int depth)
            {
                if (depth > MaximumDepth)
                    Fail("JSON exceeds the depth limit.");
                SkipWhitespace();
                if (_index >= _json.Length)
                    Fail("Unexpected end of JSON.");
                switch (_json[_index])
                {
                    case '{': return ReadObject(depth + 1);
                    case '[': return ReadArray(depth + 1);
                    case '"': return ReadString();
                    case 't': ReadLiteral("true"); return true;
                    case 'f': ReadLiteral("false"); return false;
                    case 'n': ReadLiteral("null"); return null;
                    default:
                        if (_json[_index] == '-' ||
                            (_json[_index] >= '0' && _json[_index] <= '9'))
                            return ReadNumber();
                        Fail("Unexpected JSON token.");
                        return null;
                }
            }

            private Dictionary<string, object> ReadObject(int depth)
            {
                Expect('{');
                var result = new Dictionary<string, object>(
                    StringComparer.Ordinal);
                SkipWhitespace();
                if (Take('}')) return result;
                while (true)
                {
                    SkipWhitespace();
                    if (_index >= _json.Length || _json[_index] != '"')
                        Fail("JSON object key must be a string.");
                    string key = ReadString();
                    if (result.ContainsKey(key))
                        Fail("Duplicate JSON object key: " + key);
                    SkipWhitespace();
                    Expect(':');
                    result.Add(key, ReadValue(depth));
                    SkipWhitespace();
                    if (Take('}')) return result;
                    Expect(',');
                }
            }

            private object[] ReadArray(int depth)
            {
                Expect('[');
                var result = new List<object>();
                SkipWhitespace();
                if (Take(']')) return result.ToArray();
                while (true)
                {
                    result.Add(ReadValue(depth));
                    SkipWhitespace();
                    if (Take(']')) return result.ToArray();
                    Expect(',');
                }
            }

            private string ReadString()
            {
                Expect('"');
                var result = new StringBuilder();
                while (_index < _json.Length)
                {
                    char character = _json[_index++];
                    if (character == '"') return result.ToString();
                    if (character < 0x20)
                        Fail("Unescaped control character in JSON string.");
                    if (character != '\\')
                    {
                        result.Append(character);
                        continue;
                    }
                    if (_index >= _json.Length)
                        Fail("Incomplete JSON escape.");
                    switch (_json[_index++])
                    {
                        case '"': result.Append('"'); break;
                        case '\\': result.Append('\\'); break;
                        case '/': result.Append('/'); break;
                        case 'b': result.Append('\b'); break;
                        case 'f': result.Append('\f'); break;
                        case 'n': result.Append('\n'); break;
                        case 'r': result.Append('\r'); break;
                        case 't': result.Append('\t'); break;
                        case 'u': result.Append(ReadUnicodeEscape()); break;
                        default: Fail("Invalid JSON escape."); break;
                    }
                }
                Fail("Unterminated JSON string.");
                return null;
            }

            private char ReadUnicodeEscape()
            {
                if (_index + 4 > _json.Length)
                    Fail("Incomplete Unicode escape.");
                int value = 0;
                for (int offset = 0; offset < 4; offset++)
                {
                    char digit = _json[_index++];
                    value <<= 4;
                    if (digit >= '0' && digit <= '9') value += digit - '0';
                    else if (digit >= 'a' && digit <= 'f')
                        value += digit - 'a' + 10;
                    else if (digit >= 'A' && digit <= 'F')
                        value += digit - 'A' + 10;
                    else Fail("Invalid Unicode escape.");
                }
                return (char)value;
            }

            private object ReadNumber()
            {
                int start = _index;
                Take('-');
                if (Take('0'))
                {
                    if (_index < _json.Length &&
                        char.IsDigit(_json[_index]))
                        Fail("JSON numbers cannot have leading zeros.");
                }
                else
                {
                    RequireDigit();
                    while (_index < _json.Length &&
                        char.IsDigit(_json[_index])) _index++;
                }
                bool fractional = false;
                if (Take('.'))
                {
                    fractional = true;
                    RequireDigit();
                    while (_index < _json.Length &&
                        char.IsDigit(_json[_index])) _index++;
                }
                if (_index < _json.Length &&
                    (_json[_index] == 'e' || _json[_index] == 'E'))
                {
                    fractional = true;
                    _index++;
                    if (_index < _json.Length &&
                        (_json[_index] == '+' || _json[_index] == '-'))
                        _index++;
                    RequireDigit();
                    while (_index < _json.Length &&
                        char.IsDigit(_json[_index])) _index++;
                }
                string token = _json.Substring(start, _index - start);
                if (!fractional && long.TryParse(token,
                        NumberStyles.AllowLeadingSign,
                        CultureInfo.InvariantCulture, out long integer))
                {
                    if (integer >= int.MinValue && integer <= int.MaxValue)
                        return (int)integer;
                    return integer;
                }
                if (double.TryParse(token, NumberStyles.Float,
                        CultureInfo.InvariantCulture, out double number) &&
                    !double.IsNaN(number) && !double.IsInfinity(number))
                    return number;
                Fail("Invalid JSON number.");
                return null;
            }

            private void RequireDigit()
            {
                if (_index >= _json.Length ||
                    !char.IsDigit(_json[_index]))
                    Fail("JSON number requires a digit.");
            }

            private void ReadLiteral(string literal)
            {
                if (_index + literal.Length > _json.Length ||
                    string.CompareOrdinal(_json, _index, literal, 0,
                        literal.Length) != 0)
                    Fail("Invalid JSON literal.");
                _index += literal.Length;
            }

            private void SkipWhitespace()
            {
                while (_index < _json.Length)
                {
                    char value = _json[_index];
                    if (value != ' ' && value != '\t' &&
                        value != '\r' && value != '\n') return;
                    _index++;
                }
            }

            private bool Take(char value)
            {
                if (_index >= _json.Length || _json[_index] != value)
                    return false;
                _index++;
                return true;
            }

            private void Expect(char value)
            {
                if (!Take(value))
                    Fail("Expected '" + value + "'.");
            }

            private void Fail(string message)
            {
                throw new InvalidDataException(
                    message + " (offset " + _index.ToString(
                        CultureInfo.InvariantCulture) + ")");
            }
        }
    }
}
