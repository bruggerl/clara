install:
	@python3 setup.py sdist
	@pip3 install dist/clara*.tar.gz

uninstall:
	@pip3 uninstall clara

reinstall:
	make uninstall
	make install

build:
	@python3 setup.py build

clean:
	@find . \( -name \*.pyc -o -name \*~ -o -name \*.so \) -exec rm -fv {} \;
	@find clara/ -name \*.c -exec rm -fv {} \;
	@rm -fv MANIFEST
	@rm -rvf build/ dist/
