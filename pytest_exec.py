
import sublime
import functools
import re

from collections import defaultdict

from . import formatters
from . import PyTest


from Default import exec as std_exec

TB_MODE = re.compile(r"tb[= ](.*?)\s")


def broadcast_errors(window, message):
    window.run_command("pytest_remember_errors", message)


class PytestExecCommand(std_exec.ExecCommand):

    def run(self, **kw):
        self.dots = ""

        cmd = kw['cmd']
        match = TB_MODE.search(cmd)
        mode = match.group(1) if match else 'long'
        self._tb_mode = mode
        self._tb_formatter = formatters.TB_MODES[mode]

        return super(PytestExecCommand, self).run(**kw)

    def finish(self, proc):
        super(PytestExecCommand, self).finish(proc)

        view = self.output_view

        # summary is on the last line
        summary = view.substr(view.line(view.size() - 1))
        summary = summary.replace('=', '')

        text = get_whole_text(view)
        match = re.search(r"collected (\d+) items", text)
        if match:
            sublime.status_message("Ran %s tests. %s"
                                   % (match.group(1), summary))

        broadcast_errors(self.window, {
            "errors": self.errs_by_file,
            "formatter": self._tb_mode
        })

    def append_dots(self, dot):
        self.dots += dot
        sublime.status_message("Testing " + self.dots[-400:])

        if dot in 'FX' and PyTest.Settings.get('open_panel_on_failures'):
            sublime.active_window().run_command(
                "show_panel", {"panel": "output.exec"})

    def on_data(self, proc, data):
        # print ">>", proc, ">>", data
        as_str = bytes.decode(data)
        if as_str in '.FxXs':
            sublime.set_timeout(functools.partial(self.append_dots, as_str), 0)
        super(PytestExecCommand, self).on_data(proc, data)

    def service_text_queue(self):
        self.text_queue_lock.acquire()

        is_empty = False
        try:
            if len(self.text_queue) == 0:
                # this can happen if a new build was started, which will clear
                # the text_queue
                return

            characters = self.text_queue.popleft()
            is_empty = (len(self.text_queue) == 0)
        finally:
            self.text_queue_lock.release()

        self.output_view.run_command(
            'append',
            {'characters': characters, 'force': True, 'scroll_to_end': True})



        if self.show_errors_inline and characters.find('\n') >= 0:
            self.errs_by_file = parse_output(
                self.output_view, self._tb_formatter.get_matches)

            broadcast_errors(self.window, {
                "errors": self.errs_by_file,
                "formatter": self._tb_mode,
                "intermediate": True
            })

        if not is_empty:
            sublime.set_timeout(self.service_text_queue, 1)



def get_whole_text(view):
    # type: (View) -> str

    reg = sublime.Region(0, view.size())
    return view.substr(reg)



def parse_output(view, get_matches):
    # type: (View, Callable) -> Dict[Filename, List[Tuple[Line, Column, Text]]]

    text = get_whole_text(view)
    matches = get_matches(text)

    # We still do the default regex search too bc it gets the
    # filename correct
    errs = view.find_all_results_with_text()
    assert len(matches) == len(errs)

    errs_by_file = defaultdict(list)
    for match, err in zip(matches, errs):
        (file, _, _, _) = err
        (line, text) = match
        line = int(line)
        errs_by_file[file].append((line, text))

    return errs_by_file


