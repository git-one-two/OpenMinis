#define _GNU_SOURCE
#define ARCH_ARM64 1
#include <assert.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/prctl.h>
#include <errno.h>
typedef uint64_t word_t;
enum { CURRENT, ORIGINAL, MODIFIED };
enum { SYSARG_1, SYSARG_2, SYSARG_3, SYSARG_4, SYSARG_5, SYSARG_6,
       SYSARG_NUM=8, INSTR_POINTER=32, STACK_POINTER=31 };
enum { PR_exit=93, PR_execve=221, PR_openat=56, PR_prctl=167 };
enum { ET_EXEC=2, ET_DYN=3, PT_LOAD=1, PF_X=1, WARNING=1, INTERNAL=1 };
struct user_regs_struct { word_t values[34]; };
typedef struct { int type, machine; bool class64; } ElfHeader;
typedef struct { int type, flags; word_t vaddr, memsz; } ProgramHeader;
#define IS_CLASS64(h) ((h).class64)
#define ELF_FIELD(h,f) ((h).f)
#define PROGRAM_FIELD(h,p,f) ((void)(h), (p).f)
typedef struct { word_t addr, length; } Mapping;
typedef struct LoadInfo { char *user_path, *raw_path; Mapping *mappings; struct LoadInfo *interp; } LoadInfo;
static size_t mapping_count;
#define talloc_array_length(p) ((void)(p), mapping_count)
typedef struct {
    int pid; bool is_aarch32;
    void *qemu;
    struct { void *ptracer; } as_ptracee;
    struct user_regs_struct _regs[3];
    bool _regs_were_changed;
    LoadInfo *load_info;
    struct {
        word_t initial_sp, text_start, text_end;
        unsigned retries;
        bool active, restarting, force_sysnum, retry_exec_in_flight;
        char *raw_path;
    } harmony_loader;
} Tracee;
static char *allocated[128];
static unsigned allocated_count;
static char *mock_strdup(void *ctx, const char *s) {
    (void)ctx; assert(allocated_count < 128);
    char *p=strdup(s); assert(p); allocated[allocated_count++]=p; return p;
}
static void mock_free(char *p) {
    for(unsigned i=0;i<allocated_count;i++) if(allocated[i]==p) { free(p); allocated[i]=NULL; return; }
    assert(p==NULL);
}
#define talloc_strdup(c,s) mock_strdup(c,s)
#define TALLOC_FREE(p) do { mock_free(p); (p)=NULL; } while(0)
static ElfHeader loader_header;
static ProgramHeader loader_programs[2];
static unsigned loader_program_count;
static word_t stack[16];
static int read_failure, path_failure, elf_failure, killed, notes;
static char last_path[100];
static void reset(void) {
    for(unsigned i=0;i<allocated_count;i++) free(allocated[i]);
    allocated_count=0; memset(allocated,0,sizeof allocated);
    loader_header=(ElfHeader){ET_EXEC,183,true};
    loader_programs[0]=(ProgramHeader){PT_LOAD,PF_X,0x2000000000,1128};
    loader_program_count=1; mapping_count=0; memset(stack,0,sizeof stack);
    stack[0]=2; stack[1]=0x1234; stack[2]=0x5678; stack[3]=0; stack[4]=0x9999;
    read_failure=path_failure=elf_failure=killed=notes=0;
    setenv("PROOT_VERIFY_REGSET","1",1);
    setenv("PROOT_EXEC_LOADER_RETRY","1",1);
}
static word_t peek_reg(Tracee *t,int v,int r) { return t->_regs[v].values[r]; }
static void poke_reg(Tracee *t,int r,word_t n) { t->_regs[CURRENT].values[r]=n; t->_regs_were_changed=true; }
static word_t get_sysnum(Tracee *t,int v) { return peek_reg(t,v,SYSARG_NUM); }
static void set_sysnum(Tracee *t,word_t n) { poke_reg(t,SYSARG_NUM,n); }
static int read_data(Tracee *t,void *p,word_t src,word_t n) {
    (void)t; if(read_failure || src<0x1000 || n!=8 || src-0x1000>sizeof stack-8) return -EFAULT;
    memcpy(p,(char*)stack+src-0x1000,n); return 0;
}
static int set_sysarg_path(Tracee *t,const char *p,int r) {
    poke_reg(t,STACK_POINTER,0x800); poke_reg(t,r,0x700);
    if(path_failure) return -EFAULT;
    assert(strlen(p)<sizeof last_path); strcpy(last_path,p); return 0;
}
static int open_elf(const char *p,ElfHeader *h) {
    (void)p; if(elf_failure) return -EIO; *h=loader_header; return open("/dev/null",O_RDONLY);
}
static int iterate_program_headers(Tracee *t,int fd,const ElfHeader *h,
        int (*cb)(const ElfHeader*,const ProgramHeader*,void*),void *data) {
    (void)t; (void)fd;
    for(unsigned i=0;i<loader_program_count;i++) {
        int s=cb(h,&loader_programs[i],data); if(s<0) return s;
    }
    return 0;
}
static void note(Tracee *t,int a,int b,const char *fmt,...) { (void)t;(void)a;(void)b;(void)fmt;notes++; }
static int mock_kill(int pid,int sig) { assert(pid==77&&sig==SIGKILL);killed++;return 0; }
#define kill mock_kill
