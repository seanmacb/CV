ENTRY
  { author
    title
    journal
    year
    volume
    pages
  }
  {}
  { label }

INTEGERS { output.state before.all mid.sentence after.sentence after.block }

FUNCTION {init.state.consts}
{ #0 'before.all :=
  #1 'mid.sentence :=
  #2 'after.sentence :=
  #3 'after.block :=
}

STRINGS { s t }

FUNCTION {output.nonnull}
{ 's :=
  output.state mid.sentence =
    { ", " * write$ }
    { output.state after.block =
        { add.period$ write$
          newline$
          "\newblock " write$
        }
        { output.state after.sentence =
            { " " * write$ }
            { write$ }
          if$
        }
      if$
      mid.sentence 'output.state :=
    }
  if$
  s
}

FUNCTION {output}
{ duplicate$ empty$
    { pop$ }
    { output.nonnull }
  if$
}

FUNCTION {author.fmt}
{ author empty$
    { "" }
    { author }
  if$
}

FUNCTION {article}
{ "" write$
  author.fmt output
  % Note: Nature style omits article titles
  journal empty$
    { skip$ }
    { "{\em " journal * "}" * output }
  if$
  volume empty$
    { skip$ }
    { "{\bf " volume * "}" * output }
  if$
  pages empty$
    { skip$ }
    { pages output }
  if$
  year empty$
    { skip$ }
    { "(" year * ")" * output }
  if$
  write$
  newline$
}

READ

% ==========================================================
% CRITICAL ARCHITECTURE: CHRONOLOGICAL YEAR-BASED PRESORTING
% ==========================================================
FUNCTION {presort}
{ year sortify
  "    " *         % Pad space
  author sortify *  % Fallback to author string if years match
  'sort.key$ :=
}

ITERATE {presort}

SORT

% Print the formatted data
FUNCTION {begin.bib}
{ "\begin{thebibliography}{10}" write$ newline$ }

EXECUTE {begin.bib}

EXECUTE {init.state.consts}

ITERATE {call.type$}

FUNCTION {end.bib}
{ newline$ "\end{thebibliography}" write$ newline$ }

EXECUTE {end.bib}
