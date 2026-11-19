const EARLIEST_YEAR = 1900;
const LATEST_YEAR = 2100;
const DIGITS = "0123456789";

export const DATE_RANGE = {
  min: `${EARLIEST_YEAR}-01-01`,
  max: `${LATEST_YEAR}-12-31`,
};

const SPOKEN = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "long",
  year: "numeric",
  timeZone: "UTC",
});

type DateParts = {
  year: number;
  month: number;
  day: number;
};

function isDigit(character: string): boolean {
  return DIGITS.includes(character);
}

function wholeNumber(text: string, length: number): number | null {
  const characters = [...text];

  if (characters.length !== length) {
    return null;
  }

  if (!characters.every(isDigit)) {
    return null;
  }

  return Number(text);
}

function partsOf(value: string): DateParts | null {
  const pieces = value.split("-");

  if (pieces.length !== 3) {
    return null;
  }

  const year = wholeNumber(pieces[0], 4);
  const month = wholeNumber(pieces[1], 2);
  const day = wholeNumber(pieces[2], 2);

  if (year === null || month === null || day === null) {
    return null;
  }

  return {
    year,
    month,
    day,
  };
}

function isOnCalendar(date: Date, parts: DateParts): boolean {
  const sameMonth = date.getUTCMonth() === parts.month - 1;
  const sameDay = date.getUTCDate() === parts.day;

  return sameMonth && sameDay;
}

/** "2026-10-12", as a date input gives it, becomes "12 October 2026". */
export function spokenDate(value: string): string | null {
  const parts = partsOf(value);

  if (!parts) {
    return null;
  }

  // A year typed as "26" arrives as 0026, which Date reads as 1926.
  if (parts.year < EARLIEST_YEAR || parts.year > LATEST_YEAR) {
    return null;
  }

  const time = Date.UTC(parts.year, parts.month - 1, parts.day);
  const date = new Date(time);

  if (!isOnCalendar(date, parts)) {
    return null;
  }

  return SPOKEN.format(time);
}
