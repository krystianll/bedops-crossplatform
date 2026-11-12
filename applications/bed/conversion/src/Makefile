BLDFLAGS                  = -Wall -Wextra -pedantic -std=c99
COMMONFLAGS               = -D__STDC_CONSTANT_MACROS -D_FILE_OFFSET_BITS=64 -D_LARGEFILE64_SOURCE=1
CONVERSION_CFLAGS         = -O3
CONVERSION_CDFLAGS        = -DDEBUG=1 -g -O0 -fno-inline
CONVERSION_CPFLAGS        = -pg
LIBS                      = -lpthread
MAIN                      = ../../../..
INTERFACES                = $(MAIN)/interfaces
HEAD                      = ${INTERFACES}/general-headers
INCLUDES                 := -iquote"${CURDIR}" -iquote"${HEAD}"
DISTDIR                   = ../bin
OBJDIR                    = objects${POSTFIX}
WRAPPERDIR                = wrappers
PROG                      = convert2bed
SOURCE                    = convert2bed.c
SFLAGS                    = -static
# bedops-crossplatform: Windows gives the main thread a 1 MB stack (Linux and
# macOS: 8 MB); convert2bed's threads take the same default.
ifeq ($(OS),Windows_NT)
SFLAGS += -Wl,--stack,8388608
endif

all: build

.PHONY: build build_debug build_gprof clean

build: $(DISTDIR)/$(PROG)-${BINARY_TYPE}
	rm -rf $(OBJDIR)
build_debug: $(DISTDIR)/debug.$(PROG)-${BINARY_TYPE}
	rm -rf $(OBJDIR)
build_gprof: $(DISTDIR)/gprof.$(PROG)-${BINARY_TYPE}
	rm -rf $(OBJDIR)

$(DISTDIR)/$(PROG)-${BINARY_TYPE}: $(PROG).c
	mkdir -p $(DISTDIR) && $(CC) $(BLDFLAGS) ${MEGAFLAGS} $(COMMONFLAGS) $(CFLAGS) $(CONVERSION_CFLAGS) $(SFLAGS) $(INCLUDES) $^ -o $@ $(LIBS)

$(DISTDIR)/%-${BINARY_TYPE}: %.c
	mkdir -p $(DISTDIR) && $(CC) $(BLDFLAGS) ${MEGAFLAGS} $(COMMONFLAGS) $(CFLAGS) $(CONVERSION_CFLAGS) $(SFLAGS) $(INCLUDES) $^ -o $@ $(LIBS)

$(DISTDIR)/debug.$(PROG): $(PROG).c
	mkdir -p $(DISTDIR) && $(CC) $(BLDFLAGS) ${MEGAFLAGS} $(COMMONFLAGS) $(CFLAGS) $(CONVERSION_CDFLAGS) $(SFLAGS) $(INCLUDES) $^ -o $@ $(LIBS)

$(DISTDIR)/debug.%-${BINARY_TYPE}: %.c
	mkdir -p $(DISTDIR) && $(CC) $(BLDFLAGS) ${MEGAFLAGS} $(COMMONFLAGS) $(CFLAGS) $(CONVERSION_CDFLAGS) $(SFLAGS) $(INCLUDES) $^ -o $@ $(LIBS)

$(DISTDIR)/gprof.$(PROG): $(PROG).c gprof-helper.so
	mkdir -p $(DISTDIR) && $(CC) $(BLDFLAGS) ${MEGAFLAGS} $(COMMONFLAGS) $(CFLAGS) $(CONVERSION_CPFLAGS) $(SFLAGS) $(INCLUDES) $< -o $@ $(LIBS)
	@echo -e "\nNote: To profile convert2bed with gprof/pthreads, run:\n\t$$ LD_PRELOAD=/path/to/gprof-helper.so convert2bed"

$(DISTDIR)/gprof.%-${BINARY_TYPE}: %.c gprof-helper.so
	mkdir -p $(DISTDIR) && $(CC) $(BLDFLAGS) ${MEGAFLAGS} $(COMMONFLAGS) $(CFLAGS) $(CONVERSION_CPFLAGS) $(SFLAGS) $(INCLUDES) $< -o $@ $(LIBS)
	@echo -e "\nNote: To profile convert2bed with gprof/pthreads, run:\n\t$$ LD_PRELOAD=/path/to/gprof-helper.so convert2bed"

%.so: %.c
	$(CC) -shared -fPIC $^ -o $@ $(LIBS) -ldl

# bedops-crossplatform: on Windows, build a native launcher for each bash
# wrapper (wrappers/gff2bed, ...): $(DISTDIR)/gff2bed-$(BINARY_TYPE).exe
ifeq ($(OS),Windows_NT)
WIN_WRAPPERS = $(notdir $(wildcard $(WRAPPERDIR)/*2bed $(WRAPPERDIR)/*2starch))
build: $(foreach w,$(WIN_WRAPPERS),$(DISTDIR)/$(w)-$(BINARY_TYPE).exe)

$(DISTDIR)/%-$(BINARY_TYPE).exe: c2b_wrapper_win.c
	mkdir -p $(DISTDIR) && $(CC) -Wall -Wextra -O2 -static $(CFLAGS) \
		-DC2B_WRAPPER_INPUT=\"$(word 1,$(subst 2, ,$*))\" -DC2B_WRAPPER_OUTPUT=\"$(word 2,$(subst 2, ,$*))\" $< -o $@
endif

clean:
	rm -rf $(DISTDIR)
	rm -rf $(OBJDIR)
	rm -rf  *.so *~
