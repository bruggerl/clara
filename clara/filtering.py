from clara.interpreter import RuntimeErr


class Filtering(object):
    def filter(self, progs, inter, tests, entryfnc=None, filter_regex='.*', timeout=30):
        I = inter(timeout=timeout, entryfnc=entryfnc, filter_regex=filter_regex, track=True)

        correct_progs = []

        for prog in progs:
            print(prog.name)
            correct = True

            for test in tests:
                try:
                    I.run(prog, ins=test['ins'], args=test['args'], entryfnc=entryfnc)
                except RuntimeErr as e:
                    print("EXCEPTION")
                    print(test)
                    print(e)
                    correct = False
                    break

                print("OUTPUT: " + I.output)
                print("EXPECTED: " + test['out'])
                if test['out'] is not None and test['out'] not in I.output:
                    correct = False
                    break

                if test['ret'] is not None and I.retval != test['ret']:
                    correct = False
                    break

            if correct:
                correct_progs.append(prog)

        return correct_progs
